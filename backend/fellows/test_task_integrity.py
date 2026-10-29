"""Regression coverage for task audiences, shared completion, and Google ownership."""
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .google_api import GoogleIntegrationError, sync_task_to_google
from .models import Badge, Cohort, Fellow, FellowBadge, GoogleTaskLink, Task, AvailabilityRequest


class TaskIntegrityTests(TestCase):
    def setUp(self):
        self.cohort = Cohort.objects.create(name='One', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.other = Cohort.objects.create(name='Two', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.owner = self.make_fellow('owner', self.cohort)
        self.peer = self.make_fellow('peer', self.cohort)
        self.outsider = self.make_fellow('outsider', self.other)
        self.client = APIClient()
        self.client.force_authenticate(self.owner.user)
        self.connection = patch('fellows.views.has_google_connection', return_value=False)
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def make_fellow(self, name, cohort):
        user = get_user_model().objects.create_user(username=name, email=f'{name}@example.com')
        return Fellow.objects.create(user=user, cohort=cohort)

    def task(self, **kwargs):
        values = dict(title='Assignment', cohort=self.cohort, assigned_to=self.owner, source=Task.Source.UNBOUND)
        values.update(kwargs)
        return Task.objects.create(**values)

    def url(self, task):
        return f'/api/tasks/{task.pk}/'

    def test_unbound_content_and_audience_are_protected(self):
        task = self.task()
        for payload in ({'title': 'Edited'}, {'due_date': '2026-12-01'}, {'cohort': self.other.pk}, {'scope': 'team'}, {'source': 'self'}, {'assigned_to': self.peer.pk}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch(self.url(task), payload, format='json').status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.title, 'Assignment')
        self.assertEqual(task.cohort, self.cohort)
        self.assertEqual(self.client.delete(self.url(task)).status_code, 403)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_personal_recipient_can_complete(self):
        task = self.task()
        response = self.client.patch(self.url(task), {'status': 'complete'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['can_delete'])
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETE)

    def test_shared_completion_updates_both_members_badges(self):
        badge = Badge.objects.create(name='Shared win', slug='shared-win', trigger_type=Badge.TriggerType.TASK_COUNT, required_task_count=1)
        task = self.task(scope=Task.Scope.TEAM, assigned_to=None)
        response = self.client.patch(self.url(task), {'status': 'complete'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETE)
        self.assertEqual(set(FellowBadge.objects.filter(badge=badge, earned=True).values_list('fellow_id', flat=True)), {self.owner.pk, self.peer.pk})

    def test_team_peer_can_complete_but_not_edit_or_delete_self_created_task(self):
        task = self.task(scope=Task.Scope.TEAM, source=Task.Source.SELF)
        self.client.force_authenticate(self.peer.user)
        self.assertEqual(self.client.patch(self.url(task), {'status': 'complete'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(self.url(task), {'description': 'Changed'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(self.url(task)).status_code, 403)
        self.client.force_authenticate(self.owner.user)
        self.assertEqual(self.client.patch(self.url(task), {'title': 'Creator edit'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(self.url(task)).status_code, 204)

    def test_other_cohort_cannot_see_or_mutate_shared_task(self):
        task = self.task(scope=Task.Scope.TEAM, assigned_to=None)
        self.client.force_authenticate(self.outsider.user)
        self.assertEqual(self.client.get(self.url(task)).status_code, 404)
        self.assertEqual(self.client.patch(self.url(task), {'status': 'complete'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(self.url(task)).status_code, 404)

    def test_self_created_task_cannot_move_to_another_cohort(self):
        task = self.task(source=Task.Source.SELF)
        self.assertEqual(self.client.patch(self.url(task), {'cohort': self.other.pk}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/tasks/', {'title': 'Injected audience', 'cohort': self.other.pk}, format='json').status_code, 403)

    def test_task_list_does_not_create_prototype_assignments(self):
        self.assertEqual(self.client.get('/api/tasks/').status_code, 200)
        self.assertEqual(Task.objects.count(), 0)

    def test_missing_profile_and_cohort_are_clear_errors(self):
        user = get_user_model().objects.create_user(username='no-profile')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post('/api/tasks/', {'title': 'Test'}, format='json').status_code, 403)
        Fellow.objects.create(user=user)
        self.client.force_authenticate(get_user_model().objects.get(pk=user.pk))
        response = self.client.post('/api/tasks/', {'title': 'Test', 'scope': 'team'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_availability_completion_requires_meeting_hub(self):
        meeting = AvailabilityRequest.objects.create(title='Meeting', start_date=date(2026, 11, 1), end_date=date(2026, 11, 1), cohort=self.cohort)
        meeting.create_tasks_for_fellows()
        task = Task.objects.get(availability_request=meeting, assigned_to=self.owner)
        self.assertEqual(self.client.patch(self.url(task), {'status': 'complete'}, format='json').status_code, 400)
        self.assertFalse(self.client.get(self.url(task)).data['can_change_status'])

    def test_unsafe_style_and_icon_tokens_are_rejected(self):
        for payload in ({'color': 'red;position:fixed'}, {'icon': 'fa-check" onmouseover="bad'}):
            response = self.client.post('/api/tasks/', {'title': 'Test', **payload}, format='json')
            self.assertEqual(response.status_code, 400)

    @patch('fellows.google_api._google_service')
    def test_shared_google_mirrors_are_separate_and_completed_on_first_insert(self, service_factory):
        task = self.task(scope=Task.Scope.TEAM, assigned_to=None, status=Task.Status.COMPLETE, google_task_id='unknown-legacy-owner')
        first, second = MagicMock(), MagicMock()
        first.tasks.return_value.insert.return_value.execute.return_value = {'id': 'owner-google'}
        second.tasks.return_value.insert.return_value.execute.return_value = {'id': 'peer-google'}
        service_factory.side_effect = lambda name, version, user: first if user.pk == self.owner.user_id else second
        sync_task_to_google(self.owner.user, task)
        sync_task_to_google(self.peer.user, task)
        self.assertEqual(GoogleTaskLink.objects.get(task=task, user=self.owner.user).google_task_id, 'owner-google')
        self.assertEqual(GoogleTaskLink.objects.get(task=task, user=self.peer.user).google_task_id, 'peer-google')
        self.assertEqual(first.tasks.return_value.insert.call_args.kwargs['body']['status'], 'completed')
        first.tasks.return_value.patch.assert_not_called()
        second.tasks.return_value.patch.assert_not_called()
        sync_task_to_google(self.peer.user, task)
        self.assertEqual(second.tasks.return_value.patch.call_args.kwargs['task'], 'peer-google')

    @patch('fellows.google_api._google_service')
    def test_personal_legacy_mirror_only_adopted_by_its_owner(self, service_factory):
        task = self.task(google_task_id='legacy-owned')
        sync_task_to_google(self.peer.user, task)
        service_factory.assert_not_called()
        service_factory.return_value.tasks.return_value.patch.return_value.execute.return_value = {'id': 'legacy-owned'}
        sync_task_to_google(self.owner.user, task)
        self.assertEqual(service_factory.return_value.tasks.return_value.patch.call_args.kwargs['task'], 'legacy-owned')

    @patch('fellows.google_api._google_service', side_effect=GoogleIntegrationError('Offline'))
    def test_google_outage_does_not_undo_shared_completion(self, _service):
        task = self.task(scope=Task.Scope.TEAM, assigned_to=None)
        with patch('fellows.views.has_google_connection', return_value=True):
            response = self.client.patch(self.url(task), {'status': 'complete'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETE)
