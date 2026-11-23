"""Validated operations shared by manual availability and Google Calendar sync."""

from datetime import date

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import AvailabilityRequest, AvailabilitySubmission, MeetingAvailability, Task


def request_for_fellow(fellow, request_id, *, lock=False):
    try:
        if isinstance(request_id, bool) or not request_id:
            raise ValueError
        pk = int(request_id)
    except (TypeError, ValueError):
        raise ValidationError({'request_id': 'Choose an active meeting request.'})
    requests = AvailabilityRequest.objects
    if lock:
        requests = requests.select_for_update()
    meeting = requests.filter(pk=pk, is_active=True).first()
    if not meeting or not fellow or not meeting.target_fellows().filter(pk=fellow.pk).exists():
        raise NotFound('Active availability request not found.')
    try:
        meeting.full_clean()
    except ModelValidationError:
        raise ValidationError({'request_id': 'This meeting request has an invalid date or time window. Please contact UNbound.'})
    return meeting


def validate_slot(meeting, slot):
    if not isinstance(slot, dict):
        raise ValidationError({'slots': 'Each slot must include a date, hour, and availability.'})
    raw_date = slot.get('date')
    try:
        slot_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
    except ValueError:
        slot_date = None
    if not isinstance(slot_date, date) or not meeting.start_date <= slot_date <= meeting.end_date:
        raise ValidationError({'slots': 'Every slot must be within the request date range.'})
    if meeting.selected_dates and slot_date.isoformat() not in meeting.selected_dates:
        raise ValidationError({'slots': 'Every slot must use a selected meeting date.'})
    hour = slot.get('hour')
    if type(hour) is not int or not meeting.start_hour <= hour < meeting.end_hour:
        raise ValidationError({'slots': 'Every slot must be within the request hour range.'})
    available = slot.get('is_available')
    if type(available) is not bool:
        raise ValidationError({'slots': 'Availability must be true or false.'})
    return {
        'date': slot_date,
        'hour': hour,
        'day_of_week': (slot_date.weekday() + 1) % 7,
        'is_available': available,
    }


def mark_response_draft(meeting, fellow):
    """An individual slot edit needs a fresh full-grid submission."""
    AvailabilitySubmission.objects.filter(availability_request=meeting, fellow=fellow).delete()
    Task.objects.filter(availability_request=meeting, assigned_to=fellow).update(status=Task.Status.PENDING)


@transaction.atomic
def submit_availability(fellow, request_id, slots):
    meeting = request_for_fellow(fellow, request_id, lock=True)
    expected = {
        (day, hour)
        for day in meeting.candidate_dates()
        for hour in range(meeting.start_hour, meeting.end_hour)
    }
    if not isinstance(slots, list) or len(slots) != len(expected):
        raise ValidationError({'slots': 'Submit the complete time grid, including unavailable slots.'})
    validated = [validate_slot(meeting, slot) for slot in slots]
    actual = {(slot['date'], slot['hour']) for slot in validated}
    if actual != expected:
        raise ValidationError({'slots': 'The submitted grid has duplicate or missing slots.'})

    # Validation finishes before any rows are replaced. The request lock also
    # serializes this operation with schedule edits and other submission paths.
    MeetingAvailability.objects.filter(availability_request=meeting, fellow=fellow).delete()
    saved = MeetingAvailability.objects.bulk_create([
        MeetingAvailability(availability_request=meeting, fellow=fellow, **slot)
        for slot in validated
    ])
    meeting.create_tasks_for_fellows(fellow=fellow)
    AvailabilitySubmission.objects.update_or_create(
        availability_request=meeting,
        fellow=fellow,
        defaults={'submitted_at': timezone.now()},
    )
    Task.objects.filter(availability_request=meeting, assigned_to=fellow).update(status=Task.Status.COMPLETE)
    return saved
