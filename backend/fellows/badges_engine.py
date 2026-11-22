from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AvailabilitySubmission, Badge, Fellow, FellowBadge, Task


def _progress(fellow):
    badges = list(Badge.objects.values('id', 'trigger_type', 'required_task_count', 'required_phase', 'xp_reward'))
    records = {
        record.badge_id: record
        for record in FellowBadge.objects.filter(fellow_id=fellow.pk)
    }
    rules = {badge['trigger_type'] for badge in badges}
    completed = 0
    if Badge.TriggerType.TASK_COUNT in rules:
        audience = Q(assigned_to_id=fellow.pk)
        if fellow.cohort_id:
            audience |= Q(scope=Task.Scope.TEAM, cohort_id=fellow.cohort_id)
        completed = Task.objects.filter(audience, status=Task.Status.COMPLETE).count()
    submitted = (
        Badge.TriggerType.AVAILABILITY in rules
        and AvailabilitySubmission.objects.filter(fellow_id=fellow.pk).exists()
    )
    phase = ''
    if Badge.TriggerType.PROJECT_PHASE in rules and fellow.cohort_id:
        phase = fellow.cohort.current_phase.lower()

    new_records = []
    changed_records = []
    xp = 0
    for badge in badges:
        record = records.get(badge['id'])
        missing = record is None
        if missing:
            record = FellowBadge(fellow_id=fellow.pk, badge_id=badge['id'])
        old_progress, was_earned = record.progress, record.earned
        if was_earned:
            progress = 100
        elif badge['trigger_type'] == Badge.TriggerType.TASK_COUNT:
            progress = int(min(1, completed / max(1, badge['required_task_count'])) * 100)
        elif badge['trigger_type'] == Badge.TriggerType.AVAILABILITY:
            progress = 100 if submitted else 0
        elif badge['trigger_type'] == Badge.TriggerType.PROJECT_PHASE:
            required = badge['required_phase'].lower()
            progress = 100 if required and required in phase else 0
        else:
            progress = 0

        record.progress = progress
        if progress == 100 and not was_earned:
            record.earned = True
            record.earned_at = timezone.now()
        if record.earned:
            xp += badge['xp_reward']
        if missing:
            new_records.append(record)
        elif old_progress != progress or was_earned != record.earned:
            changed_records.append(record)
    return xp, new_records, changed_records


def evaluate_and_sync_badges(fellow, *, from_read=False):
    if fellow is None:
        return 0
    if from_read:
        xp, new_records, changed_records = _progress(fellow)
        if not new_records and not changed_records and xp == fellow.xp_points:
            return xp

    # Check again after locking, since a task completion, response, or manual
    # award may have changed while this request was reading.
    with transaction.atomic():
        locked = Fellow.objects.select_for_update().get(pk=fellow.pk)
        xp, new_records, changed_records = _progress(locked)
        if new_records:
            FellowBadge.objects.bulk_create(new_records)
        if changed_records:
            FellowBadge.objects.bulk_update(changed_records, ['progress', 'earned', 'earned_at'])
        if locked.xp_points != xp:
            Fellow.objects.filter(pk=locked.pk).update(xp_points=xp)
    fellow.xp_points = xp
    return xp
