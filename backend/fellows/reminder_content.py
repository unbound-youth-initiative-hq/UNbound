from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import quote, urlencode

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.utils import timezone

from .models import Fellow, Task, availability_task_visibility_filter


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
    full_name = fellow.user.get_full_name().strip()
    first_name = fellow.user.first_name.strip() or (full_name.split()[0] if full_name else "")
    if not first_name:
        first_name = fellow.user.email.partition("@")[0] or fellow.user.username or "there"
    return assignment_check_in(first_name, tasks, now=now)


def assignment_check_in(recipient, tasks, *, now=None, assignment='assignment'):
    now = now or timezone.localtime()
    today = now.date()
    due_soon = today + timedelta(days=2)
    site_base = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    dashboard_url = f"{site_base}/dashboard/" if site_base else "/dashboard/"
    lines = [
        f"Hi {recipient},",
        "",
        (f"You have {len(tasks)} incomplete {assignment}{'s' if len(tasks) != 1 else ''}."
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


def incomplete_reminder_tasks(queryset):
    return queryset.filter(
        Q(availability_request__isnull=True) | Q(availability_request__is_active=True),
        status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
    )


def make_draft(label, addresses, subject, body):
    recipients = list({address.casefold(): address for address in addresses}.values())
    encoded_recipients = ','.join(quote(address, safe='@') for address in recipients)
    message = body.replace('\r\n', '\n').replace('\n', '\r\n')
    return {
        'label': label,
        'address': ', '.join(recipients),
        'subject': subject,
        'body': body,
        'mailto': f'mailto:{encoded_recipients}?' + urlencode({'subject': subject, 'body': message}, quote_via=quote),
    }


def task_reminder_drafts(queryset, *, now):
    """Group incomplete personal tasks by assignee and team tasks by cohort."""
    personal_tasks = defaultdict(list)
    team_tasks = defaultdict(list)
    tasks = queryset.select_related('assigned_to', 'cohort', 'availability_request')
    for task in sorted(tasks, key=pending_task_sort_key):
        team = task.scope == Task.Scope.TEAM
        recipient_id = task.cohort_id if team else task.assigned_to_id
        if recipient_id is None:
            continue
        cohort_id = task.cohort_id if team else task.assigned_to.cohort_id
        poll = task.availability_request
        if poll and not poll.assign_to_all and poll.cohort_id not in (None, cohort_id):
            continue
        (team_tasks if team else personal_tasks)[recipient_id].append(task)

    fellows = Fellow.objects.filter(
        Q(pk__in=personal_tasks) | Q(cohort_id__in=team_tasks),
        role=Fellow.Role.FELLOW,
        user__is_active=True,
    ).select_related('user').order_by('user__last_name', 'user__first_name', 'pk')
    addresses = verified_google_addresses(fellows)
    cohort_addresses = defaultdict(list)
    drafts = []
    skipped = 0
    for fellow in fellows:
        address = addresses.get(fellow.user_id)
        if not address:
            skipped += 1
            continue
        if fellow.pk in personal_tasks:
            drafts.append(make_draft(
                fellow.user.get_full_name() or fellow.user.username,
                [address],
                'Your UNbound assignment check-in',
                pending_tasks_email(fellow, personal_tasks[fellow.pk], now=now),
            ))
        if fellow.cohort_id in team_tasks:
            cohort_addresses[fellow.cohort_id].append(address)

    for cohort_id, tasks in team_tasks.items():
        recipients = cohort_addresses[cohort_id]
        if recipients:
            cohort = tasks[0].cohort.name
            drafts.append(make_draft(
                f'{cohort} cohort', recipients,
                f'UNbound team assignment check-in for {cohort}',
                assignment_check_in(f'{cohort} cohort', tasks, now=now, assignment='team assignment'),
            ))
    return drafts, skipped
