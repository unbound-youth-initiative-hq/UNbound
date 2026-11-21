"""Use actual Admin forms and portal CSRF meta/header with browser-like checks."""
import re
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from .models import Fellow


class BrowserFormTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser('operator', 'operator@example.com', 'staff-password')
        self.student = get_user_model().objects.create_user('student', 'student@example.com', 'student-password')
        Fellow.objects.create(user=self.student)
        self.browser = Client(enforce_csrf_checks=True)

    def admin_login(self):
        page = self.browser.get('/admin/login/')
        token = re.search(r'name="csrfmiddlewaretoken" value="([a-zA-Z0-9]+)"', page.content.decode())[1]
        response = self.browser.post('/admin/login/', {'username': 'operator', 'password': 'staff-password', 'csrfmiddlewaretoken': token, 'next': '/admin/'})
        self.assertEqual(response.status_code, 302)

    def test_portal_ajax_header_stays_valid_after_admin_login(self):
        self.browser.force_login(self.student)
        page = self.browser.get('/dashboard/')
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf-token" content="([a-zA-Z0-9]+)"', page.content.decode())[1]
        self.admin_login()
        response = self.browser.patch('/api/dashboard/preferences/', {'accent_palette': 'mint'}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Fellow.objects.get(user=self.student).accent_palette, 'mint')
        self.assertEqual(self.browser.get('/admin/').status_code, 200)

    def test_meeting_timezone_is_saved_for_both_dashboard_controls(self):
        self.browser.force_login(self.student)
        page = self.browser.get('/dashboard/')
        token = re.search(r'name="csrf-token" content="([a-zA-Z0-9]+)"', page.content.decode())[1]
        url = '/api/dashboard/preferences/'
        response = self.browser.patch(url, {'meeting_timezone': 'Asia/Tokyo'}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['accent_palette'], 'ocean')
        self.assertEqual(response.json()['meeting_timezone'], 'Asia/Tokyo')
        self.assertContains(self.browser.get('/dashboard/'), '<option value="Asia/Tokyo" selected>Tokyo</option>', count=2)
        response = self.browser.patch(url, {'meeting_timezone': 'Invalid/Zone'}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.browser.get(url).json()['meeting_timezone'], 'Asia/Tokyo')

    def test_actual_admin_logout_returns_to_admin_and_keeps_portal_login(self):
        self.browser.force_login(self.student)
        self.browser.get('/dashboard/')
        self.admin_login()
        page = self.browser.get('/admin/')
        token = re.search(r'name="csrfmiddlewaretoken" value="([a-zA-Z0-9]+)"', page.content.decode())[1]
        response = self.browser.post('/admin/logout/', {'csrfmiddlewaretoken': token})
        self.assertRedirects(response, '/admin/login/')
        self.assertEqual(self.browser.get('/dashboard/').status_code, 200)

    def test_expired_form_is_rejected_with_a_useful_recovery_page(self):
        response = self.browser.post('/admin/login/', {'username': 'operator', 'password': 'staff-password'})
        self.assertContains(response, 'Your last submission wasn', status_code=403)
        self.assertContains(response, 'Reopen page', status_code=403)
        self.assertEqual(self.browser.get('/admin/').status_code, 302)

    def test_api_csrf_rejection_is_readable_json_not_false_success(self):
        self.browser.force_login(self.student)
        response = self.browser.patch('/api/dashboard/preferences/', {'accent_palette': 'mint'}, content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertIn('detail', response.json())
        self.assertNotEqual(Fellow.objects.get(user=self.student).accent_palette, 'mint')
