"""Launch mode preserves local workflows without accessing Google user data."""
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from allauth.socialaccount.models import SocialAccount, SocialToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .google_api import GoogleIntegrationDisabled, get_google_credentials, has_google_connection
from .models import AvailabilityRequest, Cohort, Fellow, GoogleTaskLink, Task


@override_settings(GOOGLE_INTEGRATIONS_ENABLED=False, SOCIALACCOUNT_STORE_TOKENS=False)
class IdentityOnlyLaunchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('launch', email='launch@example.test')
        self.cohort = Cohort.objects.create(name='Launch', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.fellow = Fellow.objects.create(user=self.user, cohort=self.cohort)
        self.account = SocialAccount.objects.create(user=self.user, provider='google', uid='launch-identity')
        # Simulate a database that used the full integration build before upgrade.
        SocialToken.objects.create(account=self.account, token='synthetic-old-access', token_secret='synthetic-old-refresh')
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_oauth_redirect_cannot_request_data_scopes_even_via_query_parameters(self):
        self.client.logout()
        for process in ('login', 'connect'):
            response = self.client.get('/accounts/google/login/', {
                'process': process,
                'scope': 'https://www.googleapis.com/auth/drive.metadata.readonly',
                'auth_params': 'access_type=offline&include_granted_scopes=true&scope=https://www.googleapis.com/auth/tasks',
            })
            self.assertEqual(response.status_code, 302)
            query = parse_qs(urlsplit(response['Location']).query)
            self.assertEqual(set(query['scope'][0].split()), {'openid', 'email', 'profile'})
            self.assertEqual(query['access_type'], ['online'])
            self.assertEqual(query['prompt'], ['select_account'])
            self.assertNotIn('include_granted_scopes', query)
        self.assertFalse(settings.SOCIALACCOUNT_STORE_TOKENS)

    def test_identity_connected_without_api_token_and_deferred_ui_absent(self):
        SocialToken.objects.all().delete()
        self.assertTrue(self.client.get('/api/google/account/').json()['connected'])
        page = self.client.get('/dashboard/')
        self.assertContains(page, 'data-google-integrations-enabled="false"')
        for text in ('Meeting Hub', 'id="btnSubmitAvailability"', 'id="view-tasks"', 'id="view-badges"'):
            self.assertContains(page, text)
        for text in ('id="view-drive"', 'id="folderModal"', 'id="dashNextUpList"',
                     'id="calendarEvents"', 'id="btnSyncGoogleCalendar"',
                     'Yellow outline means', 'Connect Google to this account'):
            self.assertNotContains(page, text)

    @override_settings(GOOGLE_INTEGRATIONS_ENABLED=True)
    def test_deferred_ui_remains_available_when_explicitly_enabled(self):
        page = self.client.get('/dashboard/')
        for text in ('data-google-integrations-enabled="true"', 'id="view-drive"',
                     'id="folderModal"', 'id="dashNextUpList"', 'id="calendarEvents"',
                     'id="btnSyncGoogleCalendar"'):
            self.assertContains(page, text)

    @patch('fellows.google_api.build')
    @patch('fellows.google_api.google.auth.transport.requests.Request')
    def test_saved_tokens_and_direct_api_requests_cannot_bypass_launch_mode(self, transport, build):
        self.assertFalse(has_google_connection(self.user))
        with self.assertRaises(GoogleIntegrationDisabled):
            get_google_credentials(self.user)
        endpoints = [
            ('get', '/api/google/calendar/'), ('get', '/api/google/drive/'),
            ('get', '/api/google-drive/personal-files/'), ('get', '/api/google-drive/shared-files/'),
            ('get', '/api/google-drive/folders/'), ('post', '/api/google-drive/set-folder/'),
            ('get', '/api/google/tasks/'), ('post', '/api/google/tasks/'),
            ('patch', '/api/google/tasks/old-task/'), ('delete', '/api/google/tasks/old-task/'),
            ('post', '/api/meetings/sync-google/'),
        ]
        for method, url in endpoints:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()['code'], 'google_integrations_disabled')
        transport.assert_not_called()
        build.assert_not_called()
        self.assertEqual(SocialToken.objects.count(), 1)

    @patch('fellows.views.fetch_shared_calendar_events_in_range')
    @patch('fellows.google_api.build')
    def test_local_tasks_and_manual_poll_work_with_legacy_tokens(self, build, shared_calendar):
        created = self.client.post('/api/tasks/', {'title': 'Local task'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        task_id = created.json()['id']
        GoogleTaskLink.objects.create(task_id=task_id, user=self.user, google_task_id='old-mirror')
        url = f'/api/tasks/{task_id}/'
        self.assertEqual(self.client.patch(url, {'status': 'complete'}, format='json').status_code, 200)
        self.assertEqual(Task.objects.get(pk=task_id).status, Task.Status.COMPLETE)
        self.assertEqual(self.client.delete(url).status_code, 204)
        poll = AvailabilityRequest.objects.create(title='Launch poll', cohort=self.cohort,
            start_date=date(2026, 11, 7), end_date=date(2026, 11, 7), start_hour=9, end_hour=10)
        self.assertEqual(self.client.get('/api/meetings/requests/').status_code, 200)
        response = self.client.post('/api/meetings/bulk-save/', {
            'request_id': poll.pk,
            'slots': [{'date': '2026-11-07', 'hour': 9, 'is_available': True}],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['is_completed'])
        self.assertEqual(poll.tasks.get(assigned_to=self.fellow).status, Task.Status.COMPLETE)
        response = self.client.get('/api/meetings/group-availability/', {'request_id': poll.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get('/api/dashboard/overview/').status_code, 200)
        build.assert_not_called()
        shared_calendar.assert_not_called()
