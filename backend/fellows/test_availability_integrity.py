from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .google_api import sync_user_calendar_availability
from .models import AvailabilityRequest, AvailabilitySubmission, Cohort, Fellow, MeetingAvailability, Task


class AvailabilityIntegrityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='availability', email='fellow@example.test')
        self.cohort = Cohort.objects.create(name='A', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.fellow = Fellow.objects.create(user=self.user, cohort=self.cohort)
        self.meeting = AvailabilityRequest.objects.create(
            title='Session', cohort=self.cohort, start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 1), start_hour=9, end_hour=11,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def grid(self, available=False):
        return [{'date': '2026-11-01', 'hour': hour, 'is_available': available} for hour in (9, 10)]

    def submit(self, slots=None):
        return self.client.post('/api/meetings/bulk-save/', {
            'request_id': self.meeting.pk, 'slots': self.grid() if slots is None else slots,
        }, format='json')

    def test_all_busy_is_a_completed_response(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_completed'])
        self.assertTrue(self.meeting.submissions.filter(fellow=self.fellow).exists())
        self.assertFalse(self.meeting.availability_slots.filter(is_available=True).exists())
        self.assertEqual(self.meeting.tasks.get(assigned_to=self.fellow).status, Task.Status.COMPLETE)
        response = self.client.get('/api/meetings/requests/')
        self.assertTrue(response.data['requests'][0]['is_completed'])

    def test_specific_dates_are_used_for_personal_and_group_grids(self):
        self.meeting.end_date = date(2026, 11, 4)
        self.meeting.selected_dates = ['2026-11-01', '2026-11-04']
        self.meeting.save()
        expected = self.meeting.selected_dates
        response = self.client.get('/api/meetings/requests/').data['requests'][0]
        self.assertEqual([day['date'] for day in response['display_days']], expected)
        self.assertEqual(response['total_slots_count'], 4)
        slots = [{'date': day, 'hour': hour, 'is_available': True} for day in expected for hour in (9, 10)]
        self.assertEqual(self.submit(slots).status_code, 200)
        result = self.client.get('/api/meetings/group-availability/', {'request_id': self.meeting.pk})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([item['date'] for item in result.data['dates']], expected)
        self.assertEqual([item['available_count'] for item in result.data['matrix']], [1, 1, 1, 1])
        slots[-1]['date'] = '2026-11-03'
        self.assertEqual(self.submit(slots).status_code, 400)
        self.assertEqual(self.meeting.availability_slots.count(), 4)

    def test_invalid_payloads_do_not_erase_previous_response(self):
        self.assertEqual(self.submit(self.grid(True)).status_code, 200)
        invalid = [[], self.grid()[:1], [self.grid()[0], self.grid()[0]],
                   [{'date': '2026-11-02', 'hour': 9, 'is_available': True}, self.grid()[1]],
                   [{'date': '2026-11-01', 'hour': 8, 'is_available': True}, self.grid()[1]],
                   [{'date': '2026-11-01', 'hour': 9, 'is_available': 'false'}, self.grid()[1]]]
        for slots in invalid:
            with self.subTest(slots=slots):
                self.assertEqual(self.submit(slots).status_code, 400)
                self.assertEqual(self.meeting.availability_slots.filter(is_available=True).count(), 2)
                self.assertEqual(self.meeting.submissions.count(), 1)

    def test_other_cohort_cannot_submit_or_create_slot(self):
        other = Cohort.objects.create(name='B', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.fellow.cohort = other
        self.fellow.save()
        self.assertEqual(self.submit().status_code, 404)
        response = self.client.post('/api/meetings/', {
            'availability_request': self.meeting.pk, 'date': '2026-11-01', 'hour': 9, 'is_available': True,
        }, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(MeetingAvailability.objects.exists())

    def test_slot_update_cannot_move_request(self):
        self.submit()
        other = AvailabilityRequest.objects.create(title='Other', start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 1), start_hour=9, end_hour=11, assign_to_all=True)
        slot = self.meeting.availability_slots.first()
        response = self.client.patch(f'/api/meetings/{slot.pk}/', {'availability_request': other.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        slot.refresh_from_db()
        self.assertEqual(slot.availability_request_id, self.meeting.pk)

    def test_individual_slot_edit_requires_resubmission(self):
        self.submit()
        slot = self.meeting.availability_slots.first()
        response = self.client.patch(f'/api/meetings/{slot.pk}/', {'is_available': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.meeting.submissions.exists())
        self.assertEqual(self.meeting.tasks.get(assigned_to=self.fellow).status, Task.Status.PENDING)

    def test_window_change_resets_response_but_metadata_edit_preserves_it(self):
        self.submit()
        self.meeting.title = 'Updated session'
        self.meeting.deadline = date(2026, 10, 31)
        self.meeting.save()
        task = self.meeting.tasks.get(assigned_to=self.fellow)
        self.assertEqual(task.title, 'WhenBound: Updated session')
        self.assertEqual(task.due_date, self.meeting.deadline)
        self.assertEqual(task.status, Task.Status.COMPLETE)
        self.assertTrue(self.meeting.submissions.exists())
        self.meeting.end_hour = 12
        self.meeting.save()
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.PENDING)
        self.assertFalse(self.meeting.submissions.exists())
        self.assertFalse(self.meeting.availability_slots.exists())

    def test_new_fellow_receives_existing_request_task(self):
        new_user = get_user_model().objects.create_user(username='new')
        fellow = Fellow.objects.create(user=new_user, cohort=self.cohort)
        self.client.force_authenticate(new_user)
        self.assertEqual(self.client.get('/api/meetings/requests/').status_code, 200)
        self.assertEqual(self.meeting.tasks.filter(assigned_to=fellow).count(), 1)
        self.client.get('/api/meetings/requests/')
        self.assertEqual(self.meeting.tasks.filter(assigned_to=fellow).count(), 1)

    def test_invalid_windows_rejected(self):
        for change in ({'end_date': date(2026, 10, 31)}, {'end_date': date(2026, 12, 13)},
                       {'start_hour': 24}, {'end_hour': 25}, {'start_hour': 11}):
            with self.subTest(change=change):
                meeting = AvailabilityRequest.objects.get(pk=self.meeting.pk)
                for field, value in change.items():
                    setattr(meeting, field, value)
                with self.assertRaises(ValidationError):
                    meeting.save()

    @override_settings(GOOGLE_INTEGRATIONS_ENABLED=True)
    @patch('fellows.google_api.fetch_calendar_events_in_range')
    def test_google_sync_records_all_busy_submission(self, fetch):
        fetch.return_value = [{'start': {'date': '2026-11-01'}, 'end': {'date': '2026-11-02'}}]
        slots = sync_user_calendar_availability(self.user, request_id=self.meeting.pk)
        self.assertEqual(len(slots), 2)
        self.assertFalse(any(slot['is_available'] for slot in slots))
        self.assertEqual(AvailabilitySubmission.objects.filter(fellow=self.fellow).count(), 1)

    @override_settings(GOOGLE_INTEGRATIONS_ENABLED=True)
    @patch('fellows.google_api.fetch_calendar_events_in_range')
    def test_google_failure_preserves_previous_submission(self, fetch):
        self.submit(self.grid(True))
        fetch.side_effect = RuntimeError('Google unavailable')
        with self.assertRaises(RuntimeError):
            sync_user_calendar_availability(self.user, request_id=self.meeting.pk)
        self.assertEqual(self.meeting.availability_slots.filter(is_available=True).count(), 2)
        self.assertEqual(self.meeting.submissions.count(), 1)
