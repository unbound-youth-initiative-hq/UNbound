from django.utils import timezone
from django.db import transaction
from django.db.models import Q


@transaction.atomic
def evaluate_and_sync_badges(fellow):
    from .models import Badge, Fellow, FellowBadge, Task, AvailabilitySubmission

    if fellow is None:
        return 0
    # Serialize progress updates for this fellow so overlapping task/submission
    # requests cannot overwrite XP calculated from a newer completion.
    locked_fellow = Fellow.objects.select_for_update().get(pk=fellow.pk)

    task_audience = Q(assigned_to=fellow)
    if fellow.cohort_id:
        task_audience |= Q(scope=Task.Scope.TEAM, cohort_id=fellow.cohort_id)
    completed_task_count = Task.objects.filter(task_audience, status=Task.Status.COMPLETE).count()

    has_availability = AvailabilitySubmission.objects.filter(fellow=fellow).exists()

    badges = Badge.objects.all().order_by('order')
    total_xp = 0

    for badge in badges:
        fb, _ = FellowBadge.objects.get_or_create(fellow=fellow, badge=badge)

        if fb.earned:
            fb.progress = 100
            total_xp += badge.xp_reward
            fb.save()
            continue

        new_progress = 0
        should_unlock = False

        if badge.trigger_type == Badge.TriggerType.TASK_COUNT:
            req = max(1, badge.required_task_count)
            ratio = min(1.0, completed_task_count / req)
            new_progress = int(ratio * 100)
            if completed_task_count >= req:
                should_unlock = True

        elif badge.trigger_type == Badge.TriggerType.AVAILABILITY:
            if has_availability:
                new_progress = 100
                should_unlock = True

        elif badge.trigger_type == Badge.TriggerType.PROJECT_PHASE:
            current_phase = fellow.cohort.current_phase if fellow.cohort else ''
            if badge.required_phase and badge.required_phase.lower() in current_phase.lower():
                new_progress = 100
                should_unlock = True

        fb.progress = new_progress
        if should_unlock:
            fb.earned = True
            fb.earned_at = timezone.now()
            fb.progress = 100
            total_xp += badge.xp_reward

        fb.save()

    if locked_fellow.xp_points != total_xp:
        locked_fellow.xp_points = total_xp
        locked_fellow.save(update_fields=['xp_points'])
    fellow.xp_points = total_xp

    return total_xp
