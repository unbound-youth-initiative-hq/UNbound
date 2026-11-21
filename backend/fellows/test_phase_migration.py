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
            legacy = old.get_model('fellows', 'Cohort').objects.create(name='Demo', current_phase='Mission Build', start_date=cohort.start_date, end_date=cohort.end_date)
            user = old.get_model('auth', 'User').objects.create(username='legacy')
            fellow = old.get_model('fellows', 'Fellow').objects.create(user_id=user.pk, cohort_id=cohort.pk)
            old_badge = old.get_model('fellows', 'Badge').objects.create(name='Old award', slug='old-award')
            old.get_model('fellows', 'FellowBadge').objects.create(fellow_id=fellow.pk, badge_id=old_badge.pk, earned=True)
            old.get_model('fellows', 'Fellow').objects.filter(pk=fellow.pk).update(xp_points=300)
            request = old.get_model('fellows', 'AvailabilityRequest').objects.create(title='Existing poll', start_date=date(2026,10,1), end_date=date(2026,10,1))
            old.get_model('fellows','Task').objects.create(title='When2meet: Existing poll', assigned_to_id=fellow.pk, availability_request_id=request.pk, status='complete')
            old.get_model('fellows','MeetingAvailability').objects.create(fellow_id=fellow.pk, availability_request_id=request.pk, date=date(2026,10,1), hour=9, is_available=False)
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Cohort, AvailabilitySubmission, Badge, Fellow, FellowBadge, Phase, Task
            self.assertEqual(Cohort.objects.get(pk=legacy.pk).phase.name, 'Phase 2: Lift-off')
            self.assertEqual(list(Phase.objects.exclude(pk=Cohort.objects.get(pk=cohort.pk).phase_id)
                                 .values_list('name', flat=True)), ['Phase 1: Launchpad', 'Phase 2: Lift-off', 'Phase 3: Orbit'])
            self.assertEqual(Badge.objects.filter(trigger_type='manual').count(), 12)
            self.assertFalse(Badge.objects.filter(slug='old-award').exists())
            self.assertFalse(FellowBadge.objects.exists())
            self.assertEqual(Fellow.objects.get(pk=fellow.pk).xp_points, 0)
            self.assertTrue(Task.objects.filter(title='WhenBound: Existing poll', status='complete').exists())
            self.assertEqual(Cohort.objects.get(pk=cohort.pk).phase.name, 'Custom client phase')
            self.assertTrue(AvailabilitySubmission.objects.filter(fellow_id=fellow.pk, availability_request_id=request.pk).exists())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
