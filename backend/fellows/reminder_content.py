from collections import defaultdict
from datetime import date, timedelta

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.utils import timezone

from .models import Task, availability_task_visibility_filter


def verified_google_addresses(selected):
    accounts = SocialAccount.objects.filter(
        provider='google', user__fellow_profile__in=selected,
    ).order_by('pk').values_list('user_id', 'extra_data')
    addresses = {}
    for user_id, data in accounts:
        address = data.get('email')
        if not isinstance(address, str) or not (
            data.get('email_verified') is True or data.get('verified_email') is True
        ):
            continue
        try:
            validate_email(address)
        except ValidationError:
            continue
        addresses.setdefault(user_id, address)
    return addresses


def pending_tasks_for_fellow(fellow):
    task_filter = Q(assigned_to=fellow)
    if fellow.cohort_id:
        task_filter |= Q(scope=Task.Scope.TEAM, cohort_id=fellow.cohort_id)
    tasks = list(
        Task.objects.filter(
            task_filter,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).filter(
            availability_task_visibility_filter(fellow)
        ).select_related("availability_request").distinct()
    )
    return sorted(tasks, key=pending_task_sort_key)


def pending_task_sort_key(task):
    return (
        0 if task.source == Task.Source.UNBOUND else 1,
        0 if task.availability_request_id else 1,
        task.due_date or date.max,
        task.due_time is None,
        task.due_time,
        task.created_at,
        task.pk,
    )


def pending_tasks_email(fellow, tasks, *, now=None):
    now = now or timezone.localtime()
    today = now.date()
    due_soon = today + timedelta(days=2)

    full_name = fellow.user.get_full_name().strip()
    first_name = fellow.user.first_name.strip() or (full_name.split()[0] if full_name else "")
    if not first_name:
        first_name = fellow.user.email.partition("@")[0] or fellow.user.username or "there"

    site_base = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    dashboard_url = f"{site_base}/dashboard/" if site_base else "/dashboard/"
    lines = [
        f"Hi {first_name},",
        "",
        (f"You have {len(tasks)} incomplete assignment{'s' if len(tasks) != 1 else ''}."
         if tasks else "You're caught up with your UNbound assignments."),
        "",
    ]
    for task in tasks:
        labels = [task.get_source_display()]
        if task.availability_request_id:
            labels.insert(0, "WhenBound")
        labels.append("Team" if task.scope == Task.Scope.TEAM else "Individual")
        if task.due_date:
            overdue = task.due_date < today or (
                task.due_date == today and task.due_time is not None and task.due_time <= now.time()
            )
            if overdue:
                labels.append("Overdue")
            elif task.due_date <= due_soon:
                labels.append("Due soon")
            due = f" — due {task.due_date:%b %d, %Y}"
            if task.due_time:
                due += f" at {task.due_time:%I:%M %p} Monterrey time"
        else:
            due = ""
        lines.append(f"- [{ ' · '.join(labels) }] {task.title}{due}")
        if task.description:
            lines.append(f"  {task.description}")
    if tasks:
        lines.extend(["", "Please check any approaching deadlines when you plan your next steps."])
    lines.extend(["", f"Open your UNbound dashboard: {dashboard_url}"])
    return "\n".join(lines)


def pending_tasks_for_selection(fellows):
    """One task query for the batch, with personal and cohort visibility per fellow."""
    profiles = {fellow.pk: fellow for fellow in fellows}
    cohort_members = defaultdict(set)
    for fellow in fellows:
        if fellow.cohort_id is not None:
            cohort_members[fellow.cohort_id].add(fellow.pk)
    tasks = Task.objects.filter(
        Q(assigned_to_id__in=profiles) | Q(scope=Task.Scope.TEAM, cohort_id__in=cohort_members),
        status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
    ).select_related('availability_request')
    result = {fellow.pk: [] for fellow in fellows}
    for task in sorted(tasks, key=pending_task_sort_key):
        recipients = cohort_members[task.cohort_id].copy() if task.scope == Task.Scope.TEAM else set()
        if task.assigned_to_id in profiles:
            recipients.add(task.assigned_to_id)
        poll = task.availability_request
        for fellow_id in recipients:
            if poll and not (
                poll.is_active and (
                    poll.assign_to_all or poll.cohort_id is None
                    or poll.cohort_id == profiles[fellow_id].cohort_id
                )
            ):
                continue
            result[fellow_id].append(task)
    return result
