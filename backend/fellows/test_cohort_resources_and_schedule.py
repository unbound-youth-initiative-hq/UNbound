from datetime import UTC, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AvailabilityRequest, Cohort, ConfirmedMeeting, Fellow, SharedDriveResource, Task


class CohortResourcesAndScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.cohorts = [
            Cohort.objects.create(name=name, start_date=today, end_date=today + timedelta(days=30))
            for name in ('Demo', 'Beta', 'Other')
        ]
        cls.fellows = [
            Fellow.objects.create(user=get_user_model().objects.create_user(f'fellow-{index}'), cohort=cohort)
            for index, cohort in enumerate([*cls.cohorts, None])
        ]

    def test_shared_resources_respect_audience_and_preserve_cohort_pins(self):
        demo, beta, _ = self.cohorts
        all_resource = SharedDriveResource.objects.create(
            title='Handbook', url='https://docs.google.com/document/d/handbook/edit', audience='all',
        )
        selected = SharedDriveResource.objects.create(
            title='Workshop deck', url='https://docs.google.com/presentation/d/workshop/edit', audience='selected',
        )
        selected.cohorts.set([demo, beta])
        pin = demo.drive_links.create(
            title='Pinned draft', url='https://docs.google.com/document/d/draft/edit', pinned_by=self.fellows[0],
        )
        for index, fellow in enumerate(self.fellows):
            with self.subTest(fellow=fellow):
                self.client.force_login(fellow.user)
                page = self.client.get(reverse('dashboard-drive'))
                self.assertEqual(all_resource.url in page.content.decode(), index < 3)
                self.assertEqual(selected.url in page.content.decode(), index < 2)
                self.assertEqual(pin.url in page.content.decode(), index == 0)

        selected.is_published = False
        selected.save(update_fields=['is_published'])
        self.client.force_login(self.fellows[0].user)
        self.assertNotContains(self.client.get(reverse('dashboard-drive')), selected.url)

    def test_coordinator_can_publish_and_edit_selected_resources_in_admin(self):
        call_command('setup_staff_group', verbosity=0)
        operator = get_user_model().objects.create_user('coordinator', password='test-password', is_staff=True)
        operator.groups.add(Group.objects.get(name='UNbound coordinators'))
        self.client.post(reverse('admin:login'), {'username': operator.username, 'password': 'test-password', 'next': '/admin/'})
        url = reverse('admin:fellows_shareddriveresource_add')
        form = {
            'title': 'Cohort guide', 'url': 'https://drive.google.com/drive/folders/guide',
            'audience': 'selected', 'is_published': 'on', '_save': 'Save',
        }
        self.assertContains(self.client.post(url, form), 'Choose at least one cohort for this resource.')
        self.assertEqual(SharedDriveResource.objects.count(), 0)
        form['cohorts'] = [self.cohorts[0].pk, self.cohorts[1].pk]
        self.assertEqual(self.client.post(url, form).status_code, 302)
        resource = SharedDriveResource.objects.get()
        self.assertEqual(resource.cohorts.count(), 2)

        form['audience'] = 'all'
        self.assertEqual(self.client.post(reverse('admin:fellows_shareddriveresource_change', args=[resource.pk]), form).status_code, 302)
        resource.refresh_from_db()
        self.assertEqual(resource.audience, 'all')
        self.assertFalse(resource.cohorts.exists())

        meeting_url = reverse('admin:fellows_confirmedmeeting_add')
        date = (timezone.localdate() + timedelta(days=1)).isoformat()
        meeting_form = {
            'title': 'Demo sync', 'cohort': self.cohorts[0].pk, 'is_published': 'on',
            'starts_at_0': date, 'starts_at_1': '13:00:00', 'ends_at_0': date, 'ends_at_1': '12:00:00',
            'meet_url': 'https://meet.google.com/abc-defg-hij', '_save': 'Save',
        }
        self.assertContains(self.client.post(meeting_url, meeting_form), 'The meeting must end after it starts.')
        meeting_form['ends_at_1'] = '14:00:00'
        self.assertEqual(self.client.post(meeting_url, meeting_form).status_code, 302)
        self.assertEqual(ConfirmedMeeting.objects.get().cohort, self.cohorts[0])

    def test_meeting_dashboard_and_calendar_export_require_the_target_cohort(self):
        now = timezone.now()
        meeting = ConfirmedMeeting.objects.create(
            title='Cohort sync, review; ' + 'á' * 60, cohort=self.cohorts[0],
            starts_at=now + timedelta(hours=1), ends_at=now + timedelta(hours=2),
            meet_url='https://meet.google.com/abc-defg-hij',
        )
        url = reverse('meeting-calendar', args=[meeting.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.fellows[0].user)
        self.assertContains(self.client.get(reverse('dashboard')), meeting.meet_url)
        response = self.client.get(url)
        self.assertEqual(response['Content-Type'], 'text/calendar; charset=utf-8')
        self.assertIn('no-store', response['Cache-Control'])
        calendar = response.content.decode().replace('\r\n ', '')
        self.assertIn(f'DTSTART:{meeting.starts_at.astimezone(UTC):%Y%m%dT%H%M%SZ}', calendar)
        self.assertIn('SUMMARY:Cohort sync\\, review\\; ' + 'á' * 60, calendar)
        self.assertIn(f'LOCATION:{meeting.meet_url}', calendar)
        self.assertTrue(all(len(line) <= 75 for line in response.content.split(b'\r\n')))

        for fellow in (self.fellows[1], self.fellows[-1]):
            self.client.force_login(fellow.user)
            self.assertNotContains(self.client.get(reverse('dashboard')), meeting.meet_url)
            self.assertEqual(self.client.get(url).status_code, 404)

        meeting.is_published = False
        meeting.save(update_fields=['is_published'])
        self.client.force_login(self.fellows[0].user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_deadlines_follow_existing_task_visibility_and_exclude_completed_tasks(self):
        demo, beta, _ = self.cohorts
        today = timezone.localdate()
        overdue = Task.objects.create(title='Overdue', assigned_to=self.fellows[0], due_date=today - timedelta(days=1))
        Task.objects.create(title='Team deadline', cohort=demo, scope=Task.Scope.TEAM, due_date=today)
        Task.objects.create(title='Future due', assigned_to=self.fellows[0], due_date=today + timedelta(days=1))
        Task.objects.create(title='Complete', assigned_to=self.fellows[0], due_date=today, status=Task.Status.COMPLETE)
        Task.objects.create(title='No date', assigned_to=self.fellows[0])
        Task.objects.create(title='Other cohort due', cohort=beta, scope=Task.Scope.TEAM, due_date=today)
        poll = AvailabilityRequest.objects.create(
            title='Inactive poll', cohort=demo, start_date=today, end_date=today, is_active=False,
        )
        Task.objects.create(title='Inactive deadline', assigned_to=self.fellows[0], due_date=today, availability_request=poll)
        self.client.force_login(self.fellows[0].user)

        url = reverse('dashboard-overview-api')
        deadlines = self.client.get(url).json()['deadlines']
        self.assertEqual(deadlines['today'], today.isoformat())
        self.assertEqual([item['title'] for item in deadlines['overdue']], ['Overdue'])
        self.assertEqual([item['title'] for item in deadlines['upcoming']], ['Team deadline', 'Future due'])
        overdue.status = Task.Status.COMPLETE
        overdue.save(update_fields=['status'])
        self.assertEqual(self.client.get(url).json()['deadlines']['overdue'], [])
