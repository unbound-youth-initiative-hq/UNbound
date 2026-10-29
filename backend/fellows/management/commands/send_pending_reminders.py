from django.core.management.base import BaseCommand
from fellows.models import ReminderDelivery
from fellows.reminders import dispatch_reminders

class Command(BaseCommand):
    help = 'Process queued reminder deliveries. Interrupted/failed sends need manual review; never auto-retried.'
    def handle(self, *args, **options):
        count = dispatch_reminders(ReminderDelivery.objects.all())
        self.stdout.write(f'Processed {count} queued reminder(s).')
