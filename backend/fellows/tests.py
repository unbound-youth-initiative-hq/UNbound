from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class GoogleDashboardApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='fellow@example.com',
            email='fellow@example.com',
            password='safe-password',
        )
        self.client.force_login(self.user)

    def test_dashboard_uses_post_logout_button(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'fellow-dashboard.html')
        self.assertContains(response, 'method="post" action="/accounts/logout/"')
        self.assertContains(response, 'Google Tasks')
        self.assertNotContains(response, 'Lukah Villarreal')

    def test_login_uses_the_unbound_login_template(self):
        self.client.logout()

        response = self.client.get(reverse('account_login'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/login.html')
        self.assertContains(response, 'Fellow Login')
        self.assertContains(response, 'Sign in with Google')

    def test_google_account_endpoint_reports_unconnected_account(self):
        response = self.client.get(reverse('google-account'))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            'connected': False,
            'name': 'fellow@example.com',
            'email': 'fellow@example.com',
            'picture': '',
        })

    def test_google_calendar_requires_connection(self):
        response = self.client.get(reverse('google-calendar-events'))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['connected'], False)

    @patch('fellows.views.has_google_connection', return_value=True)
    @patch('fellows.views.fetch_calendar_events')
    def test_google_calendar_returns_events(self, fetch_events, _has_connection):
        fetch_events.return_value = [{
            'id': 'event-1',
            'summary': 'Project meeting',
            'start': {'dateTime': '2026-07-15T10:00:00-06:00'},
            'end': {'dateTime': '2026-07-15T11:00:00-06:00'},
        }]

        response = self.client.get(reverse('google-calendar-events'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['events'][0]['summary'], 'Project meeting')
        fetch_events.assert_called_once_with(self.user)

    @patch('fellows.views.has_google_connection', return_value=True)
    @patch('fellows.views.fetch_drive_files')
    def test_google_drive_uses_search_query(self, fetch_files, _has_connection):
        fetch_files.return_value = [{'id': 'file-1', 'name': 'Project plan'}]

        response = self.client.get(reverse('google-drive-files'), {'q': 'project'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['files'][0]['name'], 'Project plan')
        fetch_files.assert_called_once_with(self.user, search='project')

    @patch('fellows.views.has_google_connection', return_value=True)
    @patch('fellows.views.fetch_google_tasks')
    def test_google_tasks_returns_default_task_list(self, fetch_tasks, _has_connection):
        fetch_tasks.return_value = [{'id': 'task-1', 'title': 'Prepare notes'}]

        response = self.client.get(reverse('google-tasks'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tasks'][0]['title'], 'Prepare notes')
        fetch_tasks.assert_called_once_with(self.user)

    @patch('fellows.views.has_google_connection', return_value=True)
    @patch('fellows.views.create_google_task')
    def test_google_tasks_creates_task(self, create_task, _has_connection):
        create_task.return_value = {'id': 'task-1', 'title': 'Prepare notes'}

        response = self.client.post(
            reverse('google-tasks'),
            data={'title': 'Prepare notes'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['task']['id'], 'task-1')
        create_task.assert_called_once_with(self.user, 'Prepare notes')

    @patch('fellows.views.has_google_connection', return_value=True)
    @patch('fellows.views.update_google_task')
    def test_google_task_updates_status(self, update_task, _has_connection):
        update_task.return_value = {'id': 'task-1', 'status': 'completed'}

        response = self.client.patch(
            reverse('google-task-detail', kwargs={'task_id': 'task-1'}),
            data={'status': 'completed'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        update_task.assert_called_once_with(self.user, 'task-1', 'completed')

    @patch('fellows.views.has_google_connection', return_value=True)
    @patch('fellows.views.delete_google_task')
    def test_google_task_delete(self, delete_task, _has_connection):
        response = self.client.delete(
            reverse('google-task-detail', kwargs={'task_id': 'task-1'}),
        )

        self.assertEqual(response.status_code, 204)
        delete_task.assert_called_once_with(self.user, 'task-1')
