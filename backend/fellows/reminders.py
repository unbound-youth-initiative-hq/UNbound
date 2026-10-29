"""Durable reminder queue; an interrupted send is never automatically retried."""
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import ReminderDelivery

logger = logging.getLogger(__name__)

def dispatch_reminders(queryset):
    processed = 0
    for delivery in queryset.filter(state='queued').iterator():
        # Conditional claim works on SQLite too, and prevents two workers sending it.
        if not ReminderDelivery.objects.filter(pk=delivery.pk, state='queued').update(state='sending'):
            continue
        try:
            count = send_mail('Your pending UNbound assignments', delivery.body, None, [delivery.email], fail_silently=False)
            state = 'previewed' if settings.EMAIL_BACKEND.endswith('console.EmailBackend') else 'sent'
            if not count:
                state = 'failed'
        except Exception:
            logger.exception('Reminder delivery failed (record %s). Review before retrying.', delivery.pk)
            state = 'failed'
        ReminderDelivery.objects.filter(pk=delivery.pk).update(state=state, processed_at=timezone.now())
        processed += 1
    return processed
