import re
from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from .availability import submit_availability
from .models import (
    AvailabilityRequest, Cohort, CohortDriveLink, Fellow, InviteCode, ReminderBatch,
    SharedDriveResource, Task,
)


class PhaseOneWorkflowTests(TestCase):
    def setUp(self):
        self.today = date(2026, 11, 23)
        self.cohort = self.make_cohort('Launch')
        self.admin_client = Client(enforce_csrf_checks=True)
        operator = get_user_model().objects.create_superuser('operator', password='test-password')
        self.admin_post('/admin/login/', {'username': operator.username, 'password': 'test-password', 'next': '/admin/'})

    def make_cohort(self, name):
        return Cohort.objects.create(name=name, start_date=self.today, end_date=self.today + timedelta(days=90))

    def make_fellow(self, name, *, cohort=None, verified=True):
        user = get_user_model().objects.create_user(name, email=f'{name}@example.net', first_name=name.title())
        SocialAccount.objects.create(user=user, provider='google', uid=name, extra_data={
            'email': user.email, 'email_verified': verified,
        })
        return Fellow.objects.create(user=user, cohort=cohort)

    def admin_post(self, url, data):
        # Admin uses the session-backed token included by its real templates.
        page = self.admin_client.get('/admin/login/' if url == '/admin/login/' else '/admin/')
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content)
        self.assertIsNotNone(token)
        return self.admin_client.post(url, {**data, 'csrfmiddlewaretoken': token[1].decode()})

    def test_selected_task_drafts_group_personal_and_team_work(self):
        alex = self.make_fellow('alex', cohort=self.cohort)
        sam = self.make_fellow('sam', cohort=self.make_cohort('Orbit'))
        jay = self.make_fellow('jay', cohort=self.cohort)
        self.make_fellow('unverified', cohort=self.cohort, verified=False)
        inactive = self.make_fellow('inactive', cohort=self.cohort)
        inactive.user.is_active = False
        inactive.user.save(update_fields=['is_active'])
        timed = Task.objects.create(title='Timed past', assigned_to=alex, due_date=self.today, due_time=time(9))
        shared = Task.objects.create(
            title='Team due soon', cohort=self.cohort, scope=Task.Scope.TEAM,
            source=Task.Source.UNBOUND, due_date=self.today + timedelta(days=2),
        )
        team_notes = Task.objects.create(title='Team notes', cohort=self.cohort, scope=Task.Scope.TEAM)
        undated = Task.objects.create(title='Undated', assigned_to=alex, status=Task.Status.IN_PROGRESS)
        Task.objects.create(title='Later', assigned_to=alex, due_date=self.today + timedelta(days=3))
        finished = Task.objects.create(title='Finished', assigned_to=alex, status=Task.Status.COMPLETE)
        Task.objects.create(title='Unselected private work', assigned_to=sam)
        now = datetime.combine(self.today, time(10), tzinfo=ZoneInfo('America/Monterrey'))

        with patch('fellows.admin.timezone.localtime', return_value=now):
            response = self.admin_post(reverse('admin:fellows_task_changelist'), {
                'action': 'prepare_selected_task_drafts',
                'index': '0',
                '_selected_action': [timed.pk, shared.pk, team_notes.pk, undated.pk, finished.pk],
            })
        self.assertContains(response, 'Selected task email drafts')
        drafts = {draft['label']: draft for draft in response.context['drafts']}
        self.assertEqual(set(drafts), {'Alex', 'Launch cohort'})
        self.assertEqual(response.context['skipped'], 1)
        draft = drafts['Alex']
        self.assertIn('Hi Alex', draft['body'])
        self.assertIn('2 incomplete assignments', draft['body'])
        self.assertIn('Overdue] Timed past', draft['body'])
        self.assertIn('Individual] Undated\n', draft['body'])
        self.assertEqual(urlsplit(draft['mailto']).path, alex.user.email)
        self.assertEqual(parse_qs(urlsplit(draft['mailto']).query)['body'], [draft['body'].replace('\n', '\r\n')])
        team = drafts['Launch cohort']
        self.assertIn('Launch', team['subject'])
        self.assertIn('2 incomplete team assignments', team['body'])
        self.assertIn('Due soon] Team due soon', team['body'])
        self.assertIn('Team notes', team['body'])
        self.assertEqual(urlsplit(team['mailto']).path, f'{alex.user.email},{jay.user.email}')
        self.assertNotIn('Team notes', draft['body'])
        self.assertNotIn('Timed past', team['body'])
        for excluded in ['Finished', 'Later', 'Unselected private work', sam.user.email, inactive.user.email]:
            self.assertNotContains(response, excluded)
        self.assertFalse(ReminderBatch.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_default_task_drafts_use_overdue_deadlines_and_list_filters(self):
        alex = self.make_fellow('alex', cohort=self.cohort)
        Task.objects.create(title='Earlier today', assigned_to=alex, cohort=self.cohort, due_date=self.today, due_time=time(9))
        Task.objects.create(title='Due by end of day', assigned_to=alex, cohort=self.cohort, due_date=self.today)
        Task.objects.create(title='Due at noon', assigned_to=alex, cohort=self.cohort, due_date=self.today, due_time=time(12))
        Task.objects.create(title='Without a deadline', assigned_to=alex, cohort=self.cohort)
        Task.objects.create(
            title='Shared overdue work', cohort=self.cohort, scope=Task.Scope.TEAM,
            status=Task.Status.IN_PROGRESS, due_date=self.today - timedelta(days=1),
        )
        other = self.make_cohort('Orbit')
        sam = self.make_fellow('sam', cohort=other)
        Task.objects.create(title='Different cohort work', assigned_to=sam, cohort=other, due_date=self.today - timedelta(days=1))
        now = datetime.combine(self.today, time(10), tzinfo=ZoneInfo('America/Monterrey'))
        url = reverse('admin:fellows_task_changelist') + f'?cohort__id__exact={self.cohort.pk}'
        with patch('fellows.admin.timezone.localtime', return_value=now):
            response = self.admin_post(url, {'prepare_overdue_task_drafts': '1'})
        self.assertContains(response, 'Overdue task email drafts')
        self.assertEqual(response.context['back_url'], url)
        self.assertEqual(len(response.context['drafts']), 2)
        self.assertContains(response, 'Earlier today')
        self.assertContains(response, 'Shared overdue work')
        for excluded in ['Due by end of day', 'Due at noon', 'Without a deadline', 'Different cohort work']:
            self.assertNotContains(response, excluded)

    def test_staff_need_task_and_fellow_permissions_to_preview_task_drafts(self):
        staff = get_user_model().objects.create_user('staff', password='test-password', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='fellows', codename='view_task'))
        fellow = self.make_fellow('alex')
        task = Task.objects.create(title='Private assignment', assigned_to=fellow)
        browser = Client()
        self.assertEqual(browser.post('/admin/login/', {
            'username': staff.username, 'password': 'test-password', 'next': '/admin/',
        }).status_code, 302)
        url = reverse('admin:fellows_task_changelist')
        page = browser.get(url)
        self.assertNotContains(page, 'Email about overdue tasks')
        self.assertNotContains(page, 'Email about selected tasks')
        self.assertEqual(browser.post(url, {'prepare_overdue_task_drafts': '1'}).status_code, 403)
        response = browser.post(url, {
            'action': 'prepare_selected_task_drafts', 'index': '0', '_selected_action': [task.pk],
        })
        self.assertNotContains(response, fellow.user.email)
        self.assertEqual(browser.get(reverse('admin:fellows_fellow_send_pending_reminders')).status_code, 403)

    def test_invitation_batches_require_an_explicit_audience(self):
        url = reverse('admin:fellows_invitecode_generate')
        response = self.admin_post(url, {'audience': 'cohort'})
        self.assertContains(response, 'Choose an active cohort.')
        self.assertEqual(InviteCode.objects.count(), 0)
        self.assertEqual(self.admin_post(url, {'audience': 'cohort', 'cohort': self.cohort.pk}).status_code, 302)
        self.assertEqual(InviteCode.objects.filter(cohort=self.cohort, max_uses=1).count(), 5)
        self.assertEqual(self.admin_post(url, {'audience': 'unassigned'}).status_code, 302)
        self.assertEqual(InviteCode.objects.filter(cohort=None, max_uses=1).count(), 5)

    def test_whenbound_rechecks_responses_before_resetting_window(self):
        fellow = self.make_fellow('alex', cohort=self.cohort)
        poll = AvailabilityRequest.objects.create(
            title='Planning', cohort=self.cohort, start_date=self.today, end_date=self.today,
            start_hour=9, end_hour=10,
        )
        url = reverse('admin:fellows_availabilityrequest_change', args=[poll.pk])
        original = self.admin_client.get(url)
        key = original.context['adminform'].form['reset_snapshot'].value()
        submit_availability(fellow, poll.pk, [{'date': str(self.today), 'hour': 9, 'is_available': False}])
        fields = {
            'title': poll.title, 'cohort': self.cohort.pk, 'is_active': 'on',
            'start_date': str(self.today), 'end_date': str(self.today),
            'start_hour': '9', 'end_hour': '11', 'reset_snapshot': key, 'confirm_response_reset': 'on',
        }
        rejected = self.admin_post(url, fields)
        self.assertContains(rejected, 'confirm the reset to change the window')
        self.assertEqual(poll.submissions.count(), 1)
        self.assertEqual(poll.tasks.get().status, Task.Status.COMPLETE)

        fields['reset_snapshot'] = rejected.context['adminform'].form['reset_snapshot'].value()
        self.assertEqual(self.admin_post(url, fields).status_code, 302)
        poll.refresh_from_db()
        self.assertEqual(poll.end_hour, 11)
        self.assertEqual(poll.submissions.count(), 0)
        self.assertEqual(poll.tasks.get().status, Task.Status.PENDING)

    def test_resources_publish_and_unpublish_with_legacy_pins_intact(self):
        fellow = self.make_fellow('alex', cohort=self.cohort)
        visitor = self.make_fellow('sam', cohort=self.make_cohort('Orbit'))
        unassigned = self.make_fellow('other')
        cohort_link = CohortDriveLink.objects.create(
            cohort=self.cohort, title='Only here', url='https://example.org/guide', description='Cohort handbook',
        )
        pin = CohortDriveLink.objects.create(
            cohort=self.cohort, pinned_by=fellow, title='Pin', url='https://drive.google.com/drive/folders/abc',
        )
        payload = {
            'title': 'Workshop form', 'url': 'https://forms.gle/abc', 'description': 'RSVP for this workshop',
            'audience': 'all', 'is_published': 'on',
        }
        add_url = reverse('admin:fellows_shareddriveresource_add')
        self.assertContains(self.admin_client.get(add_url), 'data-resource-preview')
        self.assertContains(self.admin_client.get(add_url), 'resource-preview.js')
        self.assertEqual(self.admin_post(add_url, payload).status_code, 302)
        form = SharedDriveResource.objects.get()
        self.assertEqual(form.kind, 'Form')
        self.client.force_login(fellow.user)
        url = reverse('dashboard-drive')
        self.assertContains(self.client.get(url), payload['description'])
        self.assertContains(self.client.get(url), cohort_link.description)

        change_url = reverse('admin:fellows_shareddriveresource_change', args=[form.pk])
        appearance = {'resource_type_override': 'website', 'resource_icon_override': 'video'}
        self.assertEqual(self.admin_post(change_url, {**payload, **appearance}).status_code, 302)
        form.refresh_from_db()
        self.assertEqual(form.kind, 'Website')
        self.assertContains(self.admin_client.get(change_url), 'fa-video file-video')
        self.assertContains(self.client.get(url), 'fa-video file-video')
        self.assertContains(self.admin_post(change_url, {**payload, 'resource_icon_override': 'unknown'}), 'Select a valid choice')
        self.assertEqual(self.admin_post(change_url, {
            **payload, 'resource_type_override': '', 'resource_icon_override': '',
        }).status_code, 302)
        form.refresh_from_db()
        self.assertEqual(form.kind, 'Form')
        self.assertContains(self.client.get(url), 'fa-list-check file-doc')

        self.client.force_login(visitor.user)
        self.assertContains(self.client.get(url), form.url)
        self.assertNotContains(self.client.get(url), cohort_link.url)
        self.client.force_login(unassigned.user)
        self.assertNotContains(self.client.get(url), form.url)

        form.is_published = False
        form.save(update_fields=['is_published'])
        cohort_link.is_published = False
        cohort_link.save(update_fields=['is_published'])
        self.client.force_login(fellow.user)
        page = self.client.get(url)
        self.assertNotContains(page, form.url)
        self.assertNotContains(page, cohort_link.url)
        self.assertContains(page, pin.url)
