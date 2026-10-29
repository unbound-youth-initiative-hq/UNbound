from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PhaseDataMigrationTests(TransactionTestCase):
    def test_custom_phase_and_existing_response_survive_upgrade(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('fellows', '0010_expand_fellow_accent_palette')])
        try:
            old = executor.loader.project_state([('fellows', '0010_expand_fellow_accent_palette')]).apps
            cohort = old.get_model('fellows', 'Cohort').objects.create(name='Existing cohort', current_phase='Custom client phase', start_date=date(2026,1,1), end_date=date(2026,12,31))
            user = old.get_model('auth', 'User').objects.create(username='legacy')
            fellow = old.get_model('fellows', 'Fellow').objects.create(user_id=user.pk, cohort_id=cohort.pk)
            request = old.get_model('fellows', 'AvailabilityRequest').objects.create(title='Existing poll', start_date=date(2026,10,1), end_date=date(2026,10,1))
            old.get_model('fellows','Task').objects.create(title='Completed poll', assigned_to_id=fellow.pk, availability_request_id=request.pk, status='complete')
            old.get_model('fellows','MeetingAvailability').objects.create(fellow_id=fellow.pk, availability_request_id=request.pk, date=date(2026,10,1), hour=9, is_available=False)
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Cohort, AvailabilitySubmission
            self.assertEqual(Cohort.objects.get(pk=cohort.pk).phase.name, 'Custom client phase')
            self.assertTrue(AvailabilitySubmission.objects.filter(fellow_id=fellow.pk, availability_request_id=request.pk).exists())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
