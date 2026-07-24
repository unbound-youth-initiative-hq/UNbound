from django.utils import timezone

DEFAULT_BADGES = [
    {
        'name': 'Liftoff',
        'slug': 'liftoff',
        'description': 'Joined the Fellowship and set up your team.',
        'color': '#00B4D8',
        'icon_class': 'fa-paintbrush',
        'order': 1,
        'trigger_type': 'task_count',
        'required_task_count': 1,
        'xp_reward': 150,
    },
    {
        'name': 'Empathy Explorer',
        'slug': 'empathy-explorer',
        'description': 'Completed community empathy interviews.',
        'color': '#7c5cff',
        'icon_class': 'fa-magnifying-glass',
        'order': 2,
        'trigger_type': 'task_count',
        'required_task_count': 3,
        'xp_reward': 200,
    },
    {
        'name': 'Goal Setter',
        'slug': 'goal-setter',
        'description': 'Selected and mapped your project SDGs.',
        'color': '#1f9d57',
        'icon_class': 'fa-bullseye',
        'order': 3,
        'trigger_type': 'task_count',
        'required_task_count': 4,
        'xp_reward': 200,
    },
    {
        'name': 'Team Player',
        'slug': 'team-player',
        'description': 'Logged availability and synced with your cohort.',
        'color': '#e0a009',
        'icon_class': 'fa-users',
        'order': 4,
        'trigger_type': 'availability',
        'xp_reward': 200,
    },
    {
        'name': 'Builder',
        'slug': 'builder',
        'description': 'Ship your first project prototype.',
        'color': '#0090b3',
        'icon_class': 'fa-wrench',
        'order': 5,
        'trigger_type': 'task_count',
        'required_task_count': 5,
        'xp_reward': 250,
    },
    {
        'name': 'Storyteller',
        'slug': 'storyteller',
        'description': 'Deliver your Launch Sequence pitch.',
        'color': '#2a5068',
        'icon_class': 'fa-comment-dots',
        'order': 6,
        'trigger_type': 'project_phase',
        'required_phase': 'Launch Sequence',
        'xp_reward': 300,
    },
    {
        'name': 'Changemaker',
        'slug': 'changemaker',
        'description': 'Reach 100 people with your project.',
        'color': '#ef4d62',
        'icon_class': 'fa-heart',
        'order': 7,
        'trigger_type': 'task_count',
        'required_task_count': 10,
        'xp_reward': 350,
    },
    {
        'name': 'Mentor Magnet',
        'slug': 'mentor-magnet',
        'description': 'Complete all mentor 1:1 check-ins.',
        'color': '#90E0EF',
        'icon_class': 'fa-star',
        'order': 8,
        'trigger_type': 'task_count',
        'required_task_count': 7,
        'xp_reward': 250,
    },
    {
        'name': 'Touchdown',
        'slug': 'touchdown',
        'description': 'Graduate the Fellowship.',
        'color': '#167a43',
        'icon_class': 'fa-circle-check',
        'order': 9,
        'trigger_type': 'project_phase',
        'required_phase': 'Graduation',
        'xp_reward': 500,
    },
]


def ensure_default_badges_exist():
    from .models import Badge
    for item in DEFAULT_BADGES:
        Badge.objects.get_or_create(slug=item['slug'], defaults=item)


def evaluate_and_sync_badges(fellow):
    from .models import Badge, FellowBadge, Task, MeetingAvailability

    ensure_default_badges_exist()

    completed_task_count = Task.objects.filter(
        assigned_to=fellow,
        status=Task.Status.COMPLETE
    ).count()

    has_availability = MeetingAvailability.objects.filter(
        fellow=fellow,
        is_available=True
    ).exists()

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

    if fellow.xp_points != total_xp:
        fellow.xp_points = total_xp
        fellow.save(update_fields=['xp_points'])

    return total_xp