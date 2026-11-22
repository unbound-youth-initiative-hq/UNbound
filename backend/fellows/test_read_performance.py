from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .models import AvailabilityRequest, Cohort, Fellow, SDG


class RoutineReadTests(TestCase):
    def test_routine_reads_avoid_writes_and_seed_goals(self):
        today = date(2026, 11, 23)
        cohort = Cohort.objects.create(name='Launch', start_date=today, end_date=today)
        fellow = Fellow.objects.create(user=get_user_model().objects.create_user('alex'), cohort=cohort)
        Fellow.objects.create(user=get_user_model().objects.create_user('sam'), cohort=cohort)
        AvailabilityRequest.objects.create(
            title='Planning', cohort=cohort, start_date=today, end_date=today,
        )
        self.client.force_login(fellow.user)
        paths = ['/api/dashboard/overview/', '/api/badges/', '/api/meetings/requests/', '/api/cohort/sdgs/']
        self.assertEqual(self.client.get(paths[0]).json()['stats']['total_badges'], 12)
        self.assertEqual(SDG.objects.count(), 17)
        for path in paths:
            with self.subTest(path=path), CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(path).status_code, 200)
                self.assertFalse(any(query['sql'].upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))
                                     for query in queries))
                if path == paths[0]:
                    self.assertLessEqual(len(queries), 18)
