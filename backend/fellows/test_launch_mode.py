"""Launch mode preserves local workflows without accessing Google user data."""
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from allauth.socialaccount.models import SocialAccount, SocialToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .google_api import GoogleIntegrationDisabled, get_google_credentials, has_google_connection
from .models import AvailabilityRequest, Cohort, CohortDriveLink, Fellow, GoogleTaskLink, Task


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
        for text in ('Meeting Hub', 'id="btnSubmitAvailability"', 'id="view-tasks"', 'id="view-badges"',
                     'id="view-drive"', 'data-view="drive"', 'hasn’t posted any links'):
            self.assertContains(page, text)
        for text in ('id="personalFileList"', 'id="folderModal"', 'id="dashNextUpList"',
                     'id="calendarEvents"', 'id="btnSyncGoogleCalendar"',
                     'Yellow outline means', 'Connect Google to this account'):
            self.assertNotContains(page, text)

    def test_drive_resources_follow_the_signed_in_fellows_cohort(self):
        other = Cohort.objects.create(name='Other', start_date=self.cohort.start_date, end_date=self.cohort.end_date)
        folder = self.cohort.drive_links.create(title='Team <folder>', url='https://drive.google.com/drive/folders/demo?resourcekey=key')
        document = other.drive_links.create(title='Other agenda', url='https://docs.google.com/document/d/other/edit')
        page = self.client.get('/dashboard/', {'cohort': other.pk})
        self.assertContains(page, folder.url)
        self.assertContains(page, 'Team &lt;folder&gt;')
        self.assertNotContains(page, document.url)
        self.fellow.cohort = None
        self.fellow.save(update_fields=['cohort'])
        page = self.client.get('/dashboard/')
        self.assertNotContains(page, folder.url)
        self.assertNotContains(page, document.url)

    def test_drive_links_accept_only_https_google_drive_and_docs_hosts(self):
        link = CohortDriveLink(cohort=self.cohort, title='Workbook')
        for url in ('https://drive.google.com/open?id=abc', 'https://docs.google.com/spreadsheets/d/abc/edit'):
            link.url = url
            link.full_clean()
        for url in ('http://drive.google.com/open?id=abc', 'https://drive.google.com.example.org/file',
                    'https://docs.google.com@example.org/file', 'javascript:alert(1)'):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                link.url = url
                link.full_clean()

    def test_cohort_pin_shows_only_to_that_cohort_and_only_author_can_unpin(self):
        drive_url = reverse('dashboard-drive')
        coordinator_url = 'https://drive.google.com/drive/u/1/folders/resources'
        self.cohort.drive_links.create(title='Resources', url=coordinator_url)
        document = 'https://docs.google.com/document/d/example/edit?resourcekey=abc'
        form = {'title': 'Working notes', 'url': document}
        for _ in range(2):
            self.assertRedirects(self.client.post(drive_url, form), drive_url)
        pin = self.cohort.drive_links.get(pinned_by=self.fellow)
        remove_url = reverse('remove-drive-pin', args=[pin.pk])
        page = self.client.get(drive_url)
        self.assertContains(page, 'class="view active" id="view-drive"')
        self.assertContains(page, 'fa-folder file-folder')
        self.assertContains(page, 'fa-file file-doc')
        self.assertContains(page, 'Unpin Working notes')

        teammate = get_user_model().objects.create_user('teammate')
        teammate_profile = Fellow.objects.create(user=teammate, cohort=self.cohort)
        self.client.force_login(teammate)
        page = self.client.get(drive_url)
        self.assertContains(page, document)
        self.assertNotContains(page, remove_url)
        self.assertEqual(self.client.post(remove_url).status_code, 404)

        other = Cohort.objects.create(name='Other', start_date=self.cohort.start_date, end_date=self.cohort.end_date)
        teammate_profile.cohort = other
        teammate_profile.save(update_fields=['cohort'])
        page = self.client.get(drive_url)
        self.assertNotContains(page, coordinator_url)
        self.assertNotContains(page, document)

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(remove_url).status_code, 405)
        self.assertRedirects(self.client.post(remove_url), drive_url)
        self.assertFalse(self.cohort.drive_links.filter(pk=pin.pk).exists())
        self.assertNotContains(self.client.get(drive_url), document)

    def test_pins_require_membership_and_a_google_sharing_link(self):
        drive_url = reverse('dashboard-drive')
        for url in ('https://example.org/document/d/test/', 'https://drive.google.com/', 'https://docs.google.com/redirect'):
            with self.subTest(url=url):
                page = self.client.post(drive_url, {'title': 'Invalid pin', 'url': url})
                self.assertContains(page, 'class="drive-pin-form" open')
                self.assertEqual(self.cohort.drive_links.count(), 0)
        valid_url = 'https://drive.google.com/file/d/example/view'
        self.fellow.cohort = None
        self.fellow.save(update_fields=['cohort'])
        self.assertEqual(self.client.post(drive_url, {'title': 'Example', 'url': valid_url}).status_code, 403)

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
