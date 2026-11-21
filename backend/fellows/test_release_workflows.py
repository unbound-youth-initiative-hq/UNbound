from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Cohort, Fellow, Phase, SDG, Task, ReminderBatch, ReminderDelivery, InviteCode
from .reminders import dispatch_reminders


class ReleaseWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('operator', 'operator@example.com', 'test')
        self.client.force_login(self.user)
        response = self.client.post(reverse('admin:login'), {'username': 'operator', 'password': 'test', 'next': '/admin/'})
        self.assertEqual(response.status_code, 302)
        self.cohort = Cohort.objects.create(name='Pilot', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.fellow = Fellow.objects.create(user=self.user, cohort=self.cohort)

    def test_admin_workflow_pages_render_and_sensitive_fields_are_hidden(self):
        urls = ['/admin/', '/admin/fellows/cohort/', f'/admin/fellows/cohort/{self.cohort.pk}/change/', f'/admin/fellows/fellow/{self.fellow.pk}/change/', '/admin/fellows/task/assign/', '/admin/fellows/availabilityrequest/add/', '/admin/fellows/badge/add/']
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
        response = self.client.get(f'/admin/fellows/fellow/{self.fellow.pk}/change/')
        self.assertNotContains(response, 'google_access_token')
        self.assertNotContains(response, 'google_refresh_token')
        self.assertEqual(self.client.get('/admin/fellows/task/add/').status_code, 302)

    def test_overview_creates_no_assignments_and_preserves_empty_sdgs(self):
        response = self.client.get('/api/dashboard/overview/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stats']['open_tasks'], 0)
        self.assertEqual(response.json()['project_name'], '')
        self.assertEqual(response.json()['stats']['completion_pct'], 0)
        self.assertEqual(Task.objects.count(), 0)
        self.assertFalse(self.cohort.selected_sdgs.exists())

    def test_cohortless_user_has_no_unrelated_team_data(self):
        self.fellow.cohort = None
        self.fellow.save()
        other = get_user_model().objects.create_user('private', email='private@example.com')
        Fellow.objects.create(user=other, cohort=self.cohort)
        response = self.client.get('/api/dashboard/overview/')
        self.assertEqual(response.json()['team_members'], [])
        self.assertNotContains(response, 'private@example.com')

    def test_phase_rename_updates_roadmap_and_badge_rule(self):
        from .models import Badge
        phase = Phase.objects.create(name='Custom phase')
        self.cohort.phase = phase
        self.cohort.save()
        badge = Badge.objects.create(name='Progress', slug='phase-progress', required_phase=phase.name)
        phase.name = 'Renamed phase'
        phase.save()
        badge.refresh_from_db()
        self.assertEqual(badge.required_phase, phase.name)
        response = self.client.get('/api/dashboard/overview/')
        self.assertEqual(response.json()['current_phase'], phase.name)
        self.assertIn(phase.name, [p['name'] for p in response.json()['phases']])

    def test_staff_group_does_not_grant_account_or_permission_escalation(self):
        from django.contrib.auth.models import Group
        call_command('setup_staff_group', verbosity=0)
        permissions = set(Group.objects.get(name='UNbound coordinators').permissions.values_list('codename', flat=True))
        self.assertIn('add_task', permissions)
        self.assertNotIn('change_user', permissions)
        self.assertNotIn('change_permission', permissions)

    def test_coordinator_publishes_drive_folder_from_the_cohort_form(self):
        from django.contrib.auth.models import Group
        call_command('setup_staff_group', verbosity=0)
        coordinator = get_user_model().objects.create_user('coordinator', password='test', is_staff=True)
        coordinator.groups.add(Group.objects.get(name='UNbound coordinators'))
        self.client.post('/admin/logout/')
        self.client.post('/admin/login/', {'username': 'coordinator', 'password': 'test', 'next': '/admin/'})
        url = reverse('admin:fellows_cohort_change', args=[self.cohort.pk])
        self.assertContains(self.client.get(url), 'id_drive_links-TOTAL_FORMS')
        link = 'https://drive.google.com/drive/folders/sample?resourcekey=sample'
        form = {
            'name': self.cohort.name, 'start_date': self.cohort.start_date.isoformat(),
            'end_date': self.cohort.end_date.isoformat(), 'is_active': 'on',
            'drive_links-TOTAL_FORMS': '1', 'drive_links-INITIAL_FORMS': '0',
            'drive_links-0-title': 'Cohort folder', 'drive_links-0-url': link, '_save': 'Save',
        }
        self.assertEqual(self.client.post(url, form).status_code, 302)
        self.assertContains(self.client.get('/dashboard/'), link)
        resource = self.cohort.drive_links.get()
        form.update({'drive_links-INITIAL_FORMS': '1', 'drive_links-0-id': resource.pk,
                     'drive_links-0-DELETE': 'on'})
        self.assertEqual(self.client.post(url, form).status_code, 302)
        self.assertNotContains(self.client.get('/dashboard/'), link)

    def test_single_use_invitation_cannot_be_claimed_twice(self):
        from django.core.exceptions import ValidationError
        code = InviteCode.objects.create()
        stale = InviteCode.objects.get(pk=code.pk)
        code.mark_as_used(self.user)
        with self.assertRaises(ValidationError):
            stale.mark_as_used(self.user)

    def test_password_signup_cannot_bypass_invitation_registration(self):
        self.client.logout()
        response = self.client.get('/accounts/signup/')
        self.assertTemplateUsed(response, 'account/signup_closed.html')
        count = get_user_model().objects.count()
        self.client.post('/accounts/signup/', {'email': 'bypass@example.com', 'password1': 'not-a-real-password', 'password2': 'not-a-real-password'})
        self.assertEqual(get_user_model().objects.count(), count)

    def test_reminder_batch_repost_does_not_send_duplicates(self):
        Task.objects.create(title='Pending', assigned_to=self.fellow, cohort=self.cohort, source='unbound')
        url = reverse('admin:fellows_fellow_send_pending_reminders')
        response = self.client.get(url)
        self.assertContains(response, self.user.email)
        batch = ReminderBatch.objects.latest('created_at')
        with patch('fellows.reminders.send_mail', return_value=1) as mail:
            for _ in range(2):
                self.assertEqual(self.client.post(url, {'batch_id': str(batch.pk)}).status_code, 302)
            dispatch_reminders(batch.deliveries.all())
            mail.assert_called_once()
        self.assertEqual(batch.deliveries.get().state, 'sent')

    def test_failed_or_uncertain_reminders_are_never_automatically_retried(self):
        batch = ReminderBatch.objects.create(created_by=self.user)
        delivery = ReminderDelivery.objects.create(batch=batch, fellow=self.fellow, email=self.user.email, body='Pending', state='queued')
        with patch('fellows.reminders.send_mail', side_effect=TimeoutError), self.assertLogs('fellows.reminders', level='ERROR'):
            dispatch_reminders(batch.deliveries.all())
        with patch('fellows.reminders.send_mail') as mail:
            dispatch_reminders(batch.deliveries.all())
            mail.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, 'failed')
